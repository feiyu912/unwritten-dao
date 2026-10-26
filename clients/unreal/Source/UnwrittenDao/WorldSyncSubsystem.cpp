// Copyright Unwritten Dao. All Rights Reserved.

#include "WorldSyncSubsystem.h"

#include "Dom/JsonObject.h"
#include "Dom/JsonValue.h"
#include "HttpModule.h"
#include "Interfaces/IHttpResponse.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#include "TimerManager.h"
#include "UnwrittenDao.h"

namespace
{
	FString ReadString(const TSharedPtr<FJsonObject>& Object, const TCHAR* Field)
	{
		FString Value;
		if (Object.IsValid())
		{
			Object->TryGetStringField(Field, Value);
		}
		return Value;
	}

	int32 ReadInt(const TSharedPtr<FJsonObject>& Object, const TCHAR* Field, int32 Default = 0)
	{
		double Number = 0.0;
		if (Object.IsValid() && Object->TryGetNumberField(Field, Number))
		{
			return FMath::RoundToInt(Number);
		}
		return Default;
	}

	bool ReadBool(const TSharedPtr<FJsonObject>& Object, const TCHAR* Field, bool Default = false)
	{
		bool bValue = Default;
		if (Object.IsValid())
		{
			Object->TryGetBoolField(Field, bValue);
		}
		return bValue;
	}

	void ReadStringArray(const TSharedPtr<FJsonObject>& Object, const TCHAR* Field, TArray<FString>& Out)
	{
		const TArray<TSharedPtr<FJsonValue>>* Values = nullptr;
		if (Object.IsValid() && Object->TryGetArrayField(Field, Values) && Values)
		{
			for (const TSharedPtr<FJsonValue>& Value : *Values)
			{
				Out.Add(Value->AsString());
			}
		}
	}

	bool ParseJsonObject(const FString& Text, TSharedPtr<FJsonObject>& Out)
	{
		const TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(Text);
		return FJsonSerializer::Deserialize(Reader, Out) && Out.IsValid();
	}

	FString SerializeJsonObject(const TSharedPtr<FJsonObject>& Object)
	{
		FString Text;
		if (!Object.IsValid())
		{
			return TEXT("{}");
		}
		const TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&Text);
		FJsonSerializer::Serialize(Object.ToSharedRef(), Writer);
		return Text;
	}
}

void UWorldSyncSubsystem::Initialize(FSubsystemCollectionBase& Collection)
{
	Super::Initialize(Collection);
	BaseUrl.RemoveFromEnd(TEXT("/"));
}

void UWorldSyncSubsystem::Deinitialize()
{
	StopPolling();
	Super::Deinitialize();
}

void UWorldSyncSubsystem::OnWorldBeginPlay(UWorld& InWorld)
{
	Super::OnWorldBeginPlay(InWorld);
	StartPolling();
}

void UWorldSyncSubsystem::StartPolling()
{
	UWorld* World = GetWorld();
	if (!World || bPolling)
	{
		return;
	}
	bPolling = true;

	FTimerManager& Timers = World->GetTimerManager();
	Timers.SetTimer(SnapshotTimerHandle, this, &UWorldSyncSubsystem::PollSnapshot,
		FMath::Max(SnapshotPollSeconds, 0.25f), true);
	Timers.SetTimer(EventTimerHandle, this, &UWorldSyncSubsystem::PollEvents,
		FMath::Max(EventPollSeconds, 0.25f), true);

	PollSnapshot();
	PollEvents();
}

void UWorldSyncSubsystem::StopPolling()
{
	bPolling = false;
	if (UWorld* World = GetWorld())
	{
		FTimerManager& Timers = World->GetTimerManager();
		Timers.ClearTimer(SnapshotTimerHandle);
		Timers.ClearTimer(EventTimerHandle);
	}
}

void UWorldSyncSubsystem::RequestResync()
{
	bResyncRequested = true;
	RequestSnapshotNow();
}

void UWorldSyncSubsystem::RequestSnapshotNow()
{
	if (bSnapshotInFlight)
	{
		return;
	}
	bSnapshotInFlight = true;

	const TSharedRef<IHttpRequest, ESPMode::ThreadSafe> Request = FHttpModule::Get().CreateRequest();
	Request->SetURL(BaseUrl + TEXT("/v1/world/snapshot"));
	Request->SetVerb(TEXT("GET"));
	Request->SetHeader(TEXT("Accept"), TEXT("application/json"));
	Request->SetTimeout(RequestTimeoutSeconds);
	Request->OnProcessRequestComplete().BindUObject(
		this, &UWorldSyncSubsystem::HandleSnapshotResponse);

	if (!Request->ProcessRequest())
	{
		bSnapshotInFlight = false;
		UE_LOG(LogUnwrittenDao, Warning, TEXT("WorldSync: failed to dispatch snapshot request"));
	}
}

void UWorldSyncSubsystem::PollSnapshot()
{
	RequestSnapshotNow();
}

void UWorldSyncSubsystem::PollEvents()
{
	if (bEventsInFlight)
	{
		return;
	}
	bEventsInFlight = true;

	const FString Url = FString::Printf(
		TEXT("%s/v1/world/events?after=%d&limit=%d"), *BaseUrl, LastSeenEventId, EventsPageSize);
	const TSharedRef<IHttpRequest, ESPMode::ThreadSafe> Request = FHttpModule::Get().CreateRequest();
	Request->SetURL(Url);
	Request->SetVerb(TEXT("GET"));
	Request->SetHeader(TEXT("Accept"), TEXT("application/json"));
	Request->SetTimeout(RequestTimeoutSeconds);
	Request->OnProcessRequestComplete().BindUObject(
		this, &UWorldSyncSubsystem::HandleEventsResponse);

	if (!Request->ProcessRequest())
	{
		bEventsInFlight = false;
		UE_LOG(LogUnwrittenDao, Warning, TEXT("WorldSync: failed to dispatch events request"));
	}
}

void UWorldSyncSubsystem::HandleSnapshotResponse(
	FHttpRequestPtr Request, FHttpResponsePtr Response, bool bConnected)
{
	bSnapshotInFlight = false;
	if (!bConnected || !Response.IsValid())
	{
		UE_LOG(LogUnwrittenDao, Warning, TEXT("WorldSync: snapshot request did not connect"));
		return;
	}
	if (!EHttpResponseCodes::IsOk(Response->GetResponseCode()))
	{
		UE_LOG(LogUnwrittenDao, Warning, TEXT("WorldSync: snapshot HTTP %d"), Response->GetResponseCode());
		return;
	}

	TSharedPtr<FJsonObject> Root;
	if (!ParseJsonObject(Response->GetContentAsString(), Root))
	{
		UE_LOG(LogUnwrittenDao, Error, TEXT("WorldSync: snapshot JSON did not parse"));
		return;
	}

	FWorldSnapshotView Parsed;
	if (!ParseSnapshot(Root, Parsed))
	{
		UE_LOG(LogUnwrittenDao, Error, TEXT("WorldSync: snapshot missing required fields"));
		return;
	}

	// Out-of-order responses are dropped; only the server may advance the version.
	if (LatestSnapshot.bValid && Parsed.StateVersion < LatestSnapshot.StateVersion)
	{
		UE_LOG(LogUnwrittenDao, Verbose, TEXT("WorldSync: ignored stale snapshot v%d (have v%d)"),
			Parsed.StateVersion, LatestSnapshot.StateVersion);
		return;
	}

	const bool bFromResync = bResyncRequested;
	bResyncRequested = false;

	LatestSnapshot = MoveTemp(Parsed);
	LastSeenEventId = FMath::Max(LastSeenEventId, LatestSnapshot.LastEventId);
	OnSnapshotUpdated.Broadcast(LatestSnapshot, bFromResync);

	if (bPolling)
	{
		PollEvents();
	}
}

void UWorldSyncSubsystem::HandleEventsResponse(
	FHttpRequestPtr Request, FHttpResponsePtr Response, bool bConnected)
{
	bEventsInFlight = false;
	if (!bConnected || !Response.IsValid())
	{
		UE_LOG(LogUnwrittenDao, Warning, TEXT("WorldSync: events request did not connect"));
		return;
	}
	if (!EHttpResponseCodes::IsOk(Response->GetResponseCode()))
	{
		UE_LOG(LogUnwrittenDao, Warning, TEXT("WorldSync: events HTTP %d"), Response->GetResponseCode());
		return;
	}

	TSharedPtr<FJsonObject> Root;
	if (!ParseJsonObject(Response->GetContentAsString(), Root))
	{
		UE_LOG(LogUnwrittenDao, Error, TEXT("WorldSync: events JSON did not parse"));
		return;
	}

	const TArray<TSharedPtr<FJsonValue>>* Values = nullptr;
	if (!Root->TryGetArrayField(TEXT("events"), Values) || !Values)
	{
		UE_LOG(LogUnwrittenDao, Warning, TEXT("WorldSync: events response has no events array"));
		return;
	}

	TArray<FWorldEventView> Parsed;
	for (const TSharedPtr<FJsonValue>& Value : *Values)
	{
		const TSharedPtr<FJsonObject> Object = Value.IsValid() ? Value->AsObject() : nullptr;
		FWorldEventView Event;
		if (Object.IsValid() && ParseEvent(Object, Event))
		{
			Parsed.Add(MoveTemp(Event));
		}
	}

	Parsed.Sort([](const FWorldEventView& A, const FWorldEventView& B)
	{
		return A.EventId < B.EventId;
	});

	for (const FWorldEventView& Event : Parsed)
	{
		if (Event.EventId <= LastSeenEventId)
		{
			continue;
		}
		LastSeenEventId = Event.EventId;
		OnEventReceived.Broadcast(Event);
	}

	// A full page may hide more events; ask again right away.
	if (Parsed.Num() >= EventsPageSize && bPolling)
	{
		PollEvents();
	}
}

bool UWorldSyncSubsystem::ParseSnapshot(
	const TSharedPtr<FJsonObject>& Root, FWorldSnapshotView& Out) const
{
	if (!Root.IsValid())
	{
		return false;
	}

	Out.WorldId = ReadString(Root, TEXT("world_id"));
	if (Out.WorldId.IsEmpty())
	{
		return false;
	}
	Out.Tick = ReadInt(Root, TEXT("tick"));
	Out.LastEventId = ReadInt(Root, TEXT("last_event_id"));
	Out.StateVersion = ReadInt(Root, TEXT("state_version"));
	Out.bValid = true;

	const TSharedPtr<FJsonObject>* State = nullptr;
	if (!Root->TryGetObjectField(TEXT("state"), State) || !State || !State->IsValid())
	{
		return false;
	}

	Out.PlayerId = ReadString(*State, TEXT("player_id"));

	const TSharedPtr<FJsonObject>* Npcs = nullptr;
	if ((*State)->TryGetObjectField(TEXT("npcs"), Npcs) && Npcs && Npcs->IsValid())
	{
		for (const TPair<FString, TSharedPtr<FJsonValue>>& Pair : (*Npcs)->Values)
		{
			const TSharedPtr<FJsonObject> NpcObject =
				Pair.Value.IsValid() ? Pair.Value->AsObject() : nullptr;
			if (!NpcObject.IsValid())
			{
				continue;
			}
			FWorldNpcView Npc;
			Npc.NpcId = ReadString(NpcObject, TEXT("npc_id"));
			if (Npc.NpcId.IsEmpty())
			{
				Npc.NpcId = Pair.Key;
			}
			Npc.Name = ReadString(NpcObject, TEXT("name"));
			Npc.LocationId = ReadString(NpcObject, TEXT("location_id"));
			Npc.FactionId = ReadString(NpcObject, TEXT("faction_id"));
			Npc.Realm = ReadInt(NpcObject, TEXT("realm"));
			Npc.Stage = ReadInt(NpcObject, TEXT("stage"));
			Npc.bAlive = ReadBool(NpcObject, TEXT("alive"));
			Out.Npcs.Add(MoveTemp(Npc));
		}
	}

	const TSharedPtr<FJsonObject>* Locations = nullptr;
	if ((*State)->TryGetObjectField(TEXT("locations"), Locations) && Locations && Locations->IsValid())
	{
		for (const TPair<FString, TSharedPtr<FJsonValue>>& Pair : (*Locations)->Values)
		{
			const TSharedPtr<FJsonObject> LocationObject =
				Pair.Value.IsValid() ? Pair.Value->AsObject() : nullptr;
			if (!LocationObject.IsValid())
			{
				continue;
			}
			FWorldLocationView Location;
			Location.LocationId = ReadString(LocationObject, TEXT("location_id"));
			if (Location.LocationId.IsEmpty())
			{
				Location.LocationId = Pair.Key;
			}
			Location.Name = ReadString(LocationObject, TEXT("name"));
			Location.Kind = ReadString(LocationObject, TEXT("kind"));
			Out.Locations.Add(MoveTemp(Location));
		}
	}

	Out.Npcs.Sort([](const FWorldNpcView& A, const FWorldNpcView& B) { return A.NpcId < B.NpcId; });
	return true;
}

bool UWorldSyncSubsystem::ParseEvent(
	const TSharedPtr<FJsonObject>& Root, FWorldEventView& Out) const
{
	if (!Root.IsValid())
	{
		return false;
	}

	Out.EventId = ReadInt(Root, TEXT("event_id"));
	if (Out.EventId <= 0)
	{
		return false;
	}
	Out.Tick = ReadInt(Root, TEXT("tick"));
	Out.Type = ReadString(Root, TEXT("type"));
	Out.LocationId = ReadString(Root, TEXT("location_id"));
	ReadStringArray(Root, TEXT("actor_ids"), Out.ActorIds);
	ReadStringArray(Root, TEXT("target_ids"), Out.TargetIds);
	Out.StateVersionAfter = ReadInt(Root, TEXT("state_version_after"));

	const TSharedPtr<FJsonObject>* Payload = nullptr;
	if (Root->TryGetObjectField(TEXT("payload"), Payload) && Payload)
	{
		Out.PayloadJson = SerializeJsonObject(*Payload);
	}
	else
	{
		Out.PayloadJson = TEXT("{}");
	}
	return true;
}