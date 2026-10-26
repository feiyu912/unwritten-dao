// Copyright Unwritten Dao. All Rights Reserved.
// scaffold: lightweight, read-only projections of contract documents. These structs carry no
// rules; every value is copied verbatim from the authoritative server payload.

#pragma once

#include "CoreMinimal.h"
#include "WorldSyncTypes.generated.h"

/** One NPC row projected from world-snapshot.v1.state.npcs. */
USTRUCT(BlueprintType)
struct FWorldNpcView
{
	GENERATED_BODY()

	UPROPERTY(BlueprintReadOnly, Category = "World")
	FString NpcId;

	UPROPERTY(BlueprintReadOnly, Category = "World")
	FString Name;

	UPROPERTY(BlueprintReadOnly, Category = "World")
	FString LocationId;

	UPROPERTY(BlueprintReadOnly, Category = "World")
	FString FactionId;

	UPROPERTY(BlueprintReadOnly, Category = "World")
	int32 Realm = 0;

	UPROPERTY(BlueprintReadOnly, Category = "World")
	int32 Stage = 0;

	UPROPERTY(BlueprintReadOnly, Category = "World")
	bool bAlive = false;
};

/** One location row projected from world-snapshot.v1.state.locations. */
USTRUCT(BlueprintType)
struct FWorldLocationView
{
	GENERATED_BODY()

	UPROPERTY(BlueprintReadOnly, Category = "World")
	FString LocationId;

	UPROPERTY(BlueprintReadOnly, Category = "World")
	FString Name;

	UPROPERTY(BlueprintReadOnly, Category = "World")
	FString Kind;
};

/** Flattened projection of a world-snapshot.v1 document. */
USTRUCT(BlueprintType)
struct FWorldSnapshotView
{
	GENERATED_BODY()

	UPROPERTY(BlueprintReadOnly, Category = "World")
	FString WorldId;

	UPROPERTY(BlueprintReadOnly, Category = "World")
	FString PlayerId;

	UPROPERTY(BlueprintReadOnly, Category = "World")
	int32 Tick = 0;

	UPROPERTY(BlueprintReadOnly, Category = "World")
	int32 LastEventId = 0;

	UPROPERTY(BlueprintReadOnly, Category = "World")
	int32 StateVersion = 0;

	UPROPERTY(BlueprintReadOnly, Category = "World")
	bool bValid = false;

	UPROPERTY(BlueprintReadOnly, Category = "World")
	TArray<FWorldNpcView> Npcs;

	UPROPERTY(BlueprintReadOnly, Category = "World")
	TArray<FWorldLocationView> Locations;

	/** Presentation-only lookup; returns nullptr when the NPC is absent. */
	const FWorldNpcView* FindNpc(const FString& NpcId) const
	{
		return Npcs.FindByPredicate([&NpcId](const FWorldNpcView& Npc) { return Npc.NpcId == NpcId; });
	}

	/** Presentation-only lookup; returns nullptr when the location is absent. */
	const FWorldLocationView* FindLocation(const FString& LocationId) const
	{
		return Locations.FindByPredicate(
			[&LocationId](const FWorldLocationView& Loc) { return Loc.LocationId == LocationId; });
	}
};

/** Flattened projection of one world-event.v1 document. */
USTRUCT(BlueprintType)
struct FWorldEventView
{
	GENERATED_BODY()

	UPROPERTY(BlueprintReadOnly, Category = "World")
	int32 EventId = 0;

	UPROPERTY(BlueprintReadOnly, Category = "World")
	int32 Tick = 0;

	UPROPERTY(BlueprintReadOnly, Category = "World")
	FString Type;

	UPROPERTY(BlueprintReadOnly, Category = "World")
	FString LocationId;

	UPROPERTY(BlueprintReadOnly, Category = "World")
	TArray<FString> ActorIds;

	UPROPERTY(BlueprintReadOnly, Category = "World")
	TArray<FString> TargetIds;

	UPROPERTY(BlueprintReadOnly, Category = "World")
	int32 StateVersionAfter = 0;

	/** Raw JSON text of event.payload; parsed by UI code only, never interpreted as rules. */
	UPROPERTY(BlueprintReadOnly, Category = "World")
	FString PayloadJson;
};