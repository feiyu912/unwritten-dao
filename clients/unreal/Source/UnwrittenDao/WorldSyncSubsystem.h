// Copyright Unwritten Dao. All Rights Reserved.
// scaffold: UWorldSyncSubsystem is a read-only mirror of the authoritative world server.
// It fetches snapshots and event pages, projects them into lightweight structs, and
// broadcasts them. It never simulates, validates, or mutates world state.

#pragma once

#include "CoreMinimal.h"
#include "Interfaces/IHttpRequest.h"
#include "Subsystems/WorldSubsystem.h"
#include "WorldSyncTypes.h"
#include "WorldSyncSubsystem.generated.h"

DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(
	FOnWorldSnapshotUpdated, const FWorldSnapshotView&, Snapshot, bool, bFromResync);

DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(
	FOnWorldEventReceived, const FWorldEventView&, Event);

UCLASS()
class UNWRITTENDAO_API UWorldSyncSubsystem : public UWorldSubsystem
{
	GENERATED_BODY()

public:
	//~ USubsystem
	virtual void Initialize(FSubsystemCollectionBase& Collection) override;
	virtual void Deinitialize() override;
	virtual void OnWorldBeginPlay(UWorld& InWorld) override;

	/** Begin periodic snapshot + event polling (idempotent). */
	UFUNCTION(BlueprintCallable, Category = "World|Sync")
	void StartPolling();

	/** Stop all timers and in-flight polling bookkeeping. */
	UFUNCTION(BlueprintCallable, Category = "World|Sync")
	void StopPolling();

	/** Re-fetch the authoritative snapshot immediately (used after HTTP 409). */
	UFUNCTION(BlueprintCallable, Category = "World|Sync")
	void RequestResync();

	/** Fetch one snapshot immediately without changing the polling cadence. */
	UFUNCTION(BlueprintCallable, Category = "World|Sync")
	void RequestSnapshotNow();

	UFUNCTION(BlueprintPure, Category = "World|Sync")
	FString GetBaseUrl() const { return BaseUrl; }

	UFUNCTION(BlueprintPure, Category = "World|Sync")
	int32 GetStateVersion() const { return LatestSnapshot.StateVersion; }

	UFUNCTION(BlueprintPure, Category = "World|Sync")
	int32 GetLastEventId() const { return LastSeenEventId; }

	UFUNCTION(BlueprintPure, Category = "World|Sync")
	FString GetWorldId() const { return LatestSnapshot.WorldId; }

	UFUNCTION(BlueprintPure, Category = "World|Sync")
	FString GetPlayerId() const { return LatestSnapshot.PlayerId; }

	/** Last successfully parsed snapshot. bValid is false until the first success. */
	UPROPERTY(BlueprintReadOnly, Category = "World|Sync")
	FWorldSnapshotView LatestSnapshot;

	UPROPERTY(BlueprintAssignable, Category = "World|Sync")
	FOnWorldSnapshotUpdated OnSnapshotUpdated;

	UPROPERTY(BlueprintAssignable, Category = "World|Sync")
	FOnWorldEventReceived OnEventReceived;

protected:
	void PollSnapshot();
	void PollEvents();
	void HandleSnapshotResponse(FHttpRequestPtr Request, FHttpResponsePtr Response, bool bConnected);
	void HandleEventsResponse(FHttpRequestPtr Request, FHttpResponsePtr Response, bool bConnected);

	bool ParseSnapshot(const TSharedPtr<class FJsonObject>& Root, FWorldSnapshotView& Out) const;
	bool ParseEvent(const TSharedPtr<class FJsonObject>& Root, FWorldEventView& Out) const;

	/** Canonical base URL, e.g. http://127.0.0.1:8000 (no trailing slash). */
	UPROPERTY(Config, EditAnywhere, Category = "World|Sync")
	FString BaseUrl = TEXT("http://127.0.0.1:8000");

	UPROPERTY(Config, EditAnywhere, Category = "World|Sync")
	float SnapshotPollSeconds = 2.0f;

	UPROPERTY(Config, EditAnywhere, Category = "World|Sync")
	float EventPollSeconds = 1.0f;

	UPROPERTY(Config, EditAnywhere, Category = "World|Sync")
	int32 EventsPageSize = 200;

	UPROPERTY(Config, EditAnywhere, Category = "World|Sync")
	float RequestTimeoutSeconds = 10.0f;

private:
	FTimerHandle SnapshotTimerHandle;
	FTimerHandle EventTimerHandle;
	bool bSnapshotInFlight = false;
	bool bEventsInFlight = false;
	bool bPolling = false;
	bool bResyncRequested = false;
	int32 LastSeenEventId = 0;
};